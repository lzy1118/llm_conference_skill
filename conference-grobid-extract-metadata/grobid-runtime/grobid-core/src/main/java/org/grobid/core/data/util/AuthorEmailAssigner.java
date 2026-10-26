package org.grobid.core.data.util;

import java.util.List;

import org.grobid.core.data.Person;

public interface AuthorEmailAssigner {
    //embeds emails into authors
    //emails should be sanitized before
    public void assign(List<Person> authors, List<String> emails);
}
